# TariffaRadar

Osservatorio automatico delle offerte **luce, gas e telefonia mobile** in Italia, con confronto storico rispetto al costo della **materia prima**.

## Stato produzione

Il sito non usa dati dimostrativi nel frontend. Le card vengono mostrate solo se i file JSON prodotti dallo scraper contengono offerte reali.

File principali:

- `index.html`: sito statico GitHub Pages
- `scraper/`: scraper Python
- `scraper/config/providers.yaml`: configurazione fonti
- `data/offers_energy.json`: ultimo snapshot luce/gas
- `data/offers_mobile.json`: ultimo snapshot mobile
- `data/scrape_status.json`: esito generale dell'ultima scansione
- `data/scrape_report.json`: stato dettagliato fonte per fonte
- `data/history/*.json`: serie storiche per i grafici

## Scraper v2.2

La versione attuale integra solo le parti utili della v2.2, mantenendo la configurazione produzione già presente: niente dati demo, workflow robusto, backoff anti-429 e uso limitato di Energy-Charts.

| Problema | Soluzione |
|---|---|
| URL fornitori che cambiano | più URL candidati per fonte + discovery su `sitemap.xml` |
| Offerte caricate via JavaScript | Playwright/Chromium headless nel workflow |
| Cookie banner e lazy-load | click automatico sui banner più comuni + scroll progressivo |
| Markup fragile | prima JSON-LD schema.org, poi CSS + regex |
| Prezzi in centesimi | conversione automatica da c€/kWh o c€/Smc a €/unità |
| Offerte indicizzate | gestione formule `PUN + spread` e `PSV + spread` quando l'indice è disponibile |
| Debug difficile | `data/scrape_report.json` + artifact `debug-html` per le pagine lette ma vuote |
| 429 su Energy-Charts | backoff su HTTP 429 + una sola zona `IT-North` come proxy |
| Fonti non compatibili | `enabled: false` in YAML, rispettando robots.txt |

## Avvio rapido

1. Attiva GitHub Pages su branch `main`, cartella `/`.
2. Vai in **Actions** e lancia manualmente **Aggiorna offerte e indici**.
3. Dopo il run controlla:
   - `data/scrape_status.json`
   - `data/scrape_report.json`
   - artifact `debug-html`, se presente
4. Per luce/gas, se disponibile, configura `PORTALE_OPEN_DATA_URL` in `Settings -> Secrets and variables -> Actions -> Variables`.

## Workflow

```
.github/workflows/scrape.yml
        |
        v
scraper/main.py
  |- fetch_energy_offers.py   open data + pagine fornitori
  |- fetch_mobile_offers.py   pagine operatori mobile
  |- fetch_commodity.py       Energy-Charts + CSV manuale PSV/PUN
        |
        v
data/*.json
        |
        v
index.html
```

Il workflow installa Playwright, esegue lo scraper, salva il report fonti, carica eventuali HTML di debug come artifact e committa solo se i dati cambiano.

## Backfill storico elettricità

Dalla tab Actions puoi lanciare il workflow manuale compilando `backfill_from`, ad esempio:

```text
2024-01-01
```

Oppure in locale:

```bash
python -m scraper.backfill 2024-01-01
```

Il dato Energy-Charts viene salvato usando la zona `IT-North` come proxy del PUN, per evitare eccesso di chiamate API. Per valori ufficiali al dettaglio si può importare un CSV manuale in `data/manual_commodity.csv` con intestazione:

```csv
date,pun,psv
```

## Note operative

- Lo scraper legge solo pagine pubbliche o open data.
- I prezzi sono indicativi e possono essere incompleti.
- Prima di sottoscrivere un contratto, verificare sempre le condizioni ufficiali.
- Se una fonte non restituisce offerte, controllare prima `scrape_report.json`, poi l'artifact HTML di debug.
