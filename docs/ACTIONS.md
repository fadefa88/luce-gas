# GitHub Actions operative

Questo progetto è pensato per essere gestito senza eseguire script in locale.

## 1. Validare tutto

GitHub → `Actions` → `Validate data and code` → `Run workflow`.

Controlla:

- sintassi Python;
- schema JSON offerte;
- sintassi JavaScript frontend.

## 2. Audit senza commit

GitHub → `Actions` → `Audit tariff sources without commit` → `Run workflow`.

Modalità:

- `all`: ARERA luce/gas + fibra;
- `energy-only`: solo ARERA/open data;
- `fiber-only`: solo pagine ufficiali fibra.

Scarica il log da `Artifacts` a fine run. Questo workflow non modifica il repository.

## 3. Aggiornare luce/gas

GitHub → `Actions` → `Update energy data only` → `Run workflow`.

Fa import da Portale Offerte Open Data, aggiorna:

- `data/offers.json`;
- `data/commodity-index.json`;
- `data/market-correlation.json`;
- `data/offer-snapshots.json`.

Se ci sono modifiche crea commit automatico.

## 4. Aggiornare fibra

GitHub → `Actions` → `Update fiber data only` → `Run workflow`.

Fa scraping leggero delle fonti configurate in `data/sources.json`, rispetta `robots.txt`, usa delay tra richieste e salva un log come artifact.

## 5. Aggiornare tutto

GitHub → `Actions` → `Update all tariff data` → `Run workflow`.

È il workflow completo. Usalo quando vuoi aggiornare tutto insieme.

## 6. Deploy GitHub Pages

GitHub → `Settings` → `Pages` → `Build and deployment` → scegli `GitHub Actions`.

Poi usa:

GitHub → `Actions` → `Deploy static site to GitHub Pages` → `Run workflow`.

## Secret consigliato

Crea un secret repository:

```text
TARIFF_RADAR_UA=TariffRadarBot/0.3 (+https://tuodominio.it/contatti; contatto: email@dominio.it)
```

Serve per usare uno user-agent chiaro e contattabile durante lo scraping.

## ARERA 403 da GitHub Actions

Se nei log vedi `raw request blocked ... 403`, non è un errore dei due punti finali: il `: 403` è solo il codice HTTP stampato dal log. La versione aggiornata usa tre tentativi per il solo Portale Offerte Open Data:

1. richiesta HTTP trasparente con user-agent del progetto;
2. contesto browser Playwright con Chromium e cookie/referrer della pagina Open Data;
3. click browser-native sul link pubblico e cattura del download.

Nota: non impostare `TARIFF_RADAR_UA` con parole come `Bot`, `crawler` o `scraper`. Alcuni server/WAF bloccano questi user-agent anche quando il contenuto è pubblico. Il valore consigliato è:

```text
Mozilla/5.0 (compatible; TariffRadar/0.4; +https://tuodominio.it/contatti; osservatorio offerte pubbliche; contatto: tua-email@dominio.it)
```

Per il fallback browser puoi lasciare vuoto `ARERA_BROWSER_UA`: in quel caso Chromium usa il proprio user-agent nativo. Se vuoi forzarlo, crea il secret GitHub `ARERA_BROWSER_UA`.
