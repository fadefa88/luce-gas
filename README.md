# RadarTariffe

Sito statico per confrontare offerte luce, gas, fibra e mobile con storico prezzi, scadenze promo, costo annuo stimato e metodologia trasparente.

Il progetto è pensato per essere pubblicato su GitHub Pages o Cloudflare Pages senza backend. I dati sono JSON nel repository e possono essere aggiornati manualmente o tramite GitHub Actions.

## Cosa include

- Homepage production-ready responsive.
- Motore filtri per settore, profilo di consumo, ricerca e ordinamento.
- Ranking per costo annuo stimato, score, scadenza e confidenza dato.
- Grafici Canvas senza librerie esterne per storico prezzi e indice energia demo.
- Confronto rapido fino a 3 offerte.
- Alert demo lato frontend.
- Script Python per importare prezzo lancio e dati minimi da fonti configurate.
- GitHub Action giornaliera per aggiornare `data/offers.json` e `data/price-history.json`.
- Documentazione su metodologia, fonti e note legali operative.

## Struttura

```text
.
├── index.html
├── css/style.css
├── js/app.js
├── data/
│   ├── offers.json
│   ├── price-history.json
│   ├── energy-index.json
│   └── sources.example.json
├── scripts/
│   ├── import_sources.py
│   └── validate_data.py
├── docs/
│   ├── METHODOLOGY.md
│   ├── LEGAL_NOTES.md
│   └── SOURCE_TEMPLATE.md
├── .github/workflows/
│   ├── update-offers.yml
│   └── quality-check.yml
├── _headers
├── robots.txt
└── sitemap.xml
```

## Pubblicazione rapida su GitHub

1. Crea un nuovo repository GitHub, per esempio `radar-tariffe`.
2. Carica tutti i file di questa cartella nel repository.
3. Vai su **Settings → Pages**.
4. Source: **Deploy from a branch**.
5. Branch: `main`.
6. Folder: `/root`.
7. Salva.

Dopo il primo deploy il sito sarà visibile all'URL GitHub Pages.

## Pubblicazione su Cloudflare Pages

1. Cloudflare dashboard → **Workers & Pages**.
2. **Create application** → **Pages**.
3. Collega il repository GitHub.
4. Framework preset: **None**.
5. Build command: lascia vuoto.
6. Build output directory: `/`.
7. Deploy.

Il file `_headers` è già incluso per header di sicurezza base e cache differenziata su dati/statici.

## Aggiornare offerte manualmente

Modifica `data/offers.json`.

Campi minimi consigliati:

```json
{
  "id": "provider-offerta",
  "sector": "mobile",
  "provider": "Provider",
  "name": "Nome offerta",
  "status": "active",
  "priceLabel": "9,99 €/mese",
  "baseMonthly": 9.99,
  "activation": 10,
  "promoMonths": 12,
  "fullPriceAfterPromo": 12.99,
  "expiryDate": "2026-12-31",
  "sourceUrl": "https://...",
  "lastChecked": "2026-06-09",
  "confidence": 80,
  "score": 75,
  "tags": ["promo"]
}
```

Poi esegui:

```bash
python scripts/validate_data.py
```

## Import automatico fonti

Copia l'esempio:

```bash
cp data/sources.example.json data/sources.json
```

Abilita una fonte impostando:

```json
"enabled": true
```

Poi testa senza scrivere dati:

```bash
pip install -r requirements.txt
python scripts/import_sources.py --sources data/sources.json --dry-run
```

Se il risultato è corretto:

```bash
python scripts/import_sources.py --sources data/sources.json
python scripts/validate_data.py
```

## GitHub Action giornaliera

Il workflow `.github/workflows/update-offers.yml` gira ogni giorno alle 05:17 UTC e può essere lanciato manualmente da **Actions → Update offers data → Run workflow**.

Se `data/sources.json` non esiste, copia l'esempio e non importa nulla perché le fonti demo sono disabilitate.

## Regole pratiche di scraping responsabile

Il progetto non è pensato per scraping aggressivo. La configurazione e lo script seguono questi principi:

- fonti disabilitate di default;
- rispetto opzionale di `robots.txt` attivo di default;
- user-agent dichiarato;
- delay tra richieste;
- nessun login, captcha bypass, proxy rotation o aggiramento tecnico;
- import solo di dati essenziali: prezzo, attivazione, scadenza, durata promo, fonte;
- revisione manuale consigliata quando la confidenza è bassa.

Per energia luce/gas, quando possibile, preferisci open data e fonti istituzionali. Per telefonia, usa solo pagine pubbliche ufficiali e dati minimi.

## Dati demo

I dati inclusi sono dimostrativi. Prima di andare online con un servizio reale devi sostituirli con dati verificati, indicare metodologia e aggiornare link fonte.

## Prossimi step consigliati

1. Scegli nome e dominio.
2. Sostituisci `tuodominio.it` in `robots.txt`, `sitemap.xml` e README.
3. Inserisci dati reali o fonti configurate.
4. Aggiungi privacy policy e termini d'uso.
5. Collega un modulo reale per alert email.
6. Aggiungi un flusso di revisione manuale per offerte importate automaticamente.
