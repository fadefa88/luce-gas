# ⚡📶 TariffaRadar — architettura per-fornitore

Ogni fornitore (mobile, luce, gas) ha **il suo modulo Python** e **la sua
GitHub Action**: se un sito cambia si aggiusta *quel* fornitore senza toccare
gli altri, e un fornitore rotto non blocca il resto.

## Organizzazione

```
lib/base.py        fetch (requests+Playwright), modello Offer, runner, frammenti
lib/energy.py      helper prezzi luce/gas (€/kWh, centesimi, spread PUN/PSV)
lib/aggregate.py   unisce i frammenti nei file del sito

providers/mobile/<id>.py   uno per operatore -> scrape() -> [Offer]
providers/luce/<id>.py  providers/gas/<id>.py

data/providers/<cat>__<id>.json   "frammento" prodotto da ogni fornitore
data/offers_mobile.json  offers_energy.json  scrape_report.json   ricomposti
data/history/...          serie storiche per i grafici

.github/workflows/_scrape-provider.yml   workflow RIUSABILE (1 fornitore)
.github/workflows/mobile-<id>.yml ...     1 caller per fornitore
.github/workflows/aggregate.yml           ricompone i JSON del sito
.github/workflows/commodity.yml           PUN/PSV + backfill
```

### Flusso ogni ora
1. Ogni caller `mobile-<id>.yml` parte a minuto sfalsato, esegue
   `python -m providers.mobile.<id>` e committa SOLO il proprio frammento.
2. `aggregate.yml` (minuto 55) ricompone offers_mobile/energy e scrape_report.
3. `commodity.yml` (minuto 50) aggiorna PUN/PSV.
I commit usano `concurrency: data-commit` + `git pull --rebase` con retry.

## Aggiustare UN fornitore (caso d'uso principale)
1. Apri `providers/mobile/<id>.py`: ha URL, CLICKS, VERIFIED (valori a mano) e
   `parse_html(html)` = dove scrivi l'estrazione vera.
2. Lancia la sua Action, scarica l'artifact `debug-mobile__<id>` (HTML reale).
3. Implementa `parse_html()`. Finché torna vuoto, `scrape()` pubblica i VERIFIED
   (il sito resta corretto). Quando è pronto, `scrape()` restituisce i suoi dati.

Iliad è già implementato: estrae GB e prezzo dallo slug dell'URL.

## Aggiungere un fornitore
1. `providers/mobile/nuovo.py` (copia uno esistente).
2. `.github/workflows/mobile-nuovo.yml` (copia un caller, cambia id/cron).
L'aggregatore lo include da solo.

## Valori mobile pubblicati (verificati giugno 2026, solo 5G)
Iliad, Vodafone, TIM, WindTre, Fastweb, ho., Kena, Very, CoopVoce, spusu,
Lycamobile, 1Mobile, Tiscali, Sky. PosteMobile/Digi/Optima/Noitel/Vianova
predisposti, in attesa di dati.

## Energia
Moduli luce/ e gas/ sono scaffold con parse_html() da implementare. La via più
robusta resta l'open data ARERA del Portale Offerte.
