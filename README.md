# TariffaRadar

Osservatorio automatico delle offerte **luce, gas e telefonia mobile** in Italia,
con confronto storico rispetto al costo della **materia prima** (PUN per
l'elettricità, PSV per il gas).

- Sito statico servito da **GitHub Pages** (`index.html`)
- **GitHub Action** che aggiorna periodicamente i dati (`.github/workflows/scrape.yml`)
- Scraper Python config-driven (`scraper/`)
- Grafici storici (Chart.js) offerte vs indici all'ingrosso
- Nessun dato personale: si leggono solo pagine pubbliche di listino e, per luce/gas, open data quando disponibili

---

## Stato produzione

Il sito non usa più dati dimostrativi nel frontend. I file principali sono:

- `data/offers_energy.json`: ultimo snapshot luce/gas prodotto dallo scraper
- `data/offers_mobile.json`: ultimo snapshot mobile prodotto dallo scraper
- `data/scrape_status.json`: esito dell'ultima scansione
- `data/history/*.json`: serie storiche giornaliere usate dai grafici

Se gli scraper non hanno ancora rilevato offerte valide, il sito mostra uno stato di attesa invece di card inventate.

## Avvio rapido

1. Attiva GitHub Pages: `Settings -> Pages -> Source: Deploy from a branch`, branch `main`, cartella `/ (root)`.
2. Vai nella tab **Actions** e lancia manualmente il workflow **Aggiorna offerte e indici**.
3. Per luce/gas, configura la variabile consigliata `PORTALE_OPEN_DATA_URL` in `Settings -> Secrets and variables -> Actions -> Variables` con il link al CSV open data del Portale Offerte.
4. Dopo il primo run controlla `data/scrape_status.json` e i log della Action.

## Come funziona

```
.github/workflows/scrape.yml     cron orario + avvio manuale
        |
        v
scraper/main.py
  |- fetch_energy_offers.py   luce/gas: open data -> fallback pagine fornitori
  |- fetch_mobile_offers.py   mobile: pagine pubbliche operatori
  |- fetch_commodity.py       PUN GME + CSV manuale PSV/storico
        |
        v
data/offers_energy.json
data/offers_mobile.json
data/scrape_status.json
data/history/*.json
        |
        v
index.html                     card, KPI, ticker e grafici
```

Lo storico salva un record al giorno con minimo, media e numero offerte, così il repository resta leggero anche dopo anni.

## Personalizzare i fornitori

Tutto in `scraper/config/providers.yaml`: per ogni operatore indichi URL della pagina offerte, selettore CSS dei blocchi e regex per prezzo/GB. I siti commerciali cambiano spesso markup: quando un operatore sparisce dai dati, in genere basta aggiornare `selector`, `price_regex`, `gb_regex` o `name_selector`.

Alcuni siti caricano le offerte via JavaScript. In quel caso il download HTML semplice può non bastare. Le opzioni sono: usare operatori con pagine statiche, aggiungere Playwright, oppure per luce/gas preferire l'open data del Portale Offerte.

## Materia prima

- **PUN**: lo scraper tenta di leggere il dato giornaliero pubblicato dal GME e lo converte in €/kWh.
- **PSV e storico passato**: puoi importare una serie manuale creando `data/manual_commodity.csv` con intestazione `date,pun,psv`.

## Note legali e operative

- Lo scraper legge solo pagine pubbliche di listino o open data.
- I prezzi sono rilevazioni automatiche a scopo informativo.
- Prima di sottoscrivere un contratto, verifica sempre le condizioni sul sito ufficiale del fornitore o sul Portale Offerte.
- Se un sito blocca o non gradisce la rilevazione automatica, rimuovilo dal file YAML.

## Limiti noti

- I selettori CSS sono da rifinire dopo i primi run reali.
- Le offerte mobile riservate ad alcuni operatori di provenienza possono non comparire sulle pagine pubbliche.
- Alcune pagine richiedono JavaScript e potrebbero restituire zero offerte senza Playwright.
