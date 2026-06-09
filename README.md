# Tariff Radar

Static intelligence site for Italian public offers: mobile, fiber, electricity and gas.

This version intentionally avoids the usual soft SaaS look: hard grid, market tape, sharp cards, terminal panels, source-first layout.

## What is included

- Production-ready static site: `index.html`, `css/style.css`, `js/app.js`
- Real initial seed dataset in `data/offers.json`
- Official-source links on every offer
- Price history and energy index sample series
- Importer script for:
  - ARERA / Portale Offerte Open Data discovery
  - light extraction of price launch from official telco/energy pages
- GitHub Actions for scheduled update and data validation
- Legal/methodology documentation

## Important

The seed dataset is based on public official pages captured on `2026-06-09`. Prices can change. The site is designed to show **source, last check and confidence** so that users verify the official page before signing anything.

## Local preview

```bash
python -m http.server 8080
```

Open:

```text
http://localhost:8080
```

## Update real sources

Copy the example source configuration:

```bash
cp data/sources.example.json data/sources.json
```

Edit:

```json
"userAgent": "TariffRadarBot/0.2 (+https://yourdomain.example/method; contact: you@example.com)"
```

Dry run:

```bash
pip install -r requirements.txt
python scripts/import_sources.py --sources data/sources.json --dry-run
```

Write output:

```bash
python scripts/import_sources.py --sources data/sources.json --output data/offers.json
python scripts/validate_data.py
```

## GitHub Pages

Use repository root as Pages source.

## Cloudflare Pages

- Framework preset: None
- Build command: empty
- Output directory: `/`

## Data model

Each offer has:

```json
{
  "id": "very-599-150gb",
  "provider": "Very Mobile",
  "name": "Very 5,99",
  "sector": "mobile",
  "baseMonthly": 5.99,
  "activation": 0,
  "expiryDate": "2026-06-25",
  "allowance": "150 GB 5G, minuti e SMS illimitati",
  "sourceUrl": "https://...",
  "lastChecked": "2026-06-09",
  "score": 92,
  "confidence": 84
}
```

## Scraping rules

The importer is deliberately conservative:

- respects robots.txt by default;
- no login;
- no captcha bypass;
- no proxy rotation;
- no image/banner copy;
- only essential commercial data;
- source link retained.

For energy, prefer ARERA / Acquirente Unico open data where possible.
