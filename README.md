# ⚡ TariffaRadar

Osservatorio automatico delle offerte **luce, gas e telefonia mobile** in Italia,
con confronto storico rispetto al costo della **materia prima** (PUN per
l'elettricità, PSV per il gas).

- 🌐 Sito statico servito da **GitHub Pages** (`index.html`)
- 🤖 **GitHub Action** che ogni ora aggiorna i dati (`.github/workflows/scrape.yml`)
- 🐍 Scraper Python leggero e config-driven (`scraper/`)
- 📈 Grafici storici (Chart.js) offerte vs indici all'ingrosso
- 🔒 Nessun dato personale: si leggono **solo le pagine pubbliche di listino**,
  rispettando `robots.txt`, con User-Agent trasparente

---

## Avvio rapido

1. **Crea il repository** su GitHub e carica questi file (branch `main`).
2. **Attiva GitHub Pages**: `Settings → Pages → Source: Deploy from a branch`,
   branch `main`, cartella `/ (root)`.
3. **Abilita le Actions**: alla prima visita della tab *Actions* conferma
   l'esecuzione dei workflow. Puoi lanciare subito un aggiornamento manuale con
   *Run workflow* su "Aggiorna offerte e indici".
4. (Consigliato) **Configura la fonte ufficiale ARERA**: vai su
   `Settings → Secrets and variables → Actions → Variables` e crea la variabile
   `PORTALE_OPEN_DATA_URL` con il link al dataset CSV della sezione
   [Open Data del Portale Offerte](https://www.ilportaleofferte.it/portaleOfferte/it/open-data.page).
   È la fonte più completa e stabile per luce e gas (i venditori sono obbligati
   a pubblicarvi tutte le offerte) e ti evita di dipendere dallo scraping dei
   siti commerciali.

Il sito è subito visibile con **dati dimostrativi**; al primo run della Action i
file in `data/` vengono sostituiti dai dati reali.

## Come funziona

```
.github/workflows/scrape.yml     cron ogni ora (minuto 07)
        │
        ▼
scraper/main.py
  ├─ fetch_energy_offers.py   luce+gas: open data ARERA → fallback pagine fornitori
  ├─ fetch_mobile_offers.py   mobile: pagina principale offerte di ogni operatore
  └─ fetch_commodity.py       PUN dal GME (XML pubblico) + PSV/CSV manuale
        │
        ▼
data/offers_energy.json        snapshot offerte luce/gas
data/offers_mobile.json        snapshot offerte mobile
data/history/*.json            storici giornalieri (min/media) — alimentano i grafici
        │
        ▼  commit automatico
index.html (GitHub Pages)      legge i JSON e disegna card + grafici
```

Lo **storico** salva un record al giorno con minimo e media (non l'intero
snapshot orario), così il repository resta leggero anche dopo anni.

## Personalizzare i fornitori

Tutto in `scraper/config/providers.yaml`: per ogni operatore indichi URL della
pagina offerte, selettore CSS dei blocchi e regex per prezzo/GB. I siti
commerciali cambiano spesso markup: quando un operatore "sparisce" dai dati,
in genere basta aggiornare lì `selector` o le regex, senza toccare il codice.

⚠️ Alcuni siti (es. grandi operatori telefonici) caricano le offerte via
JavaScript: in quel caso il semplice download HTML non basta. Le opzioni sono
(a) preferire gli operatori con pagine statiche, (b) aggiungere Playwright al
workflow, oppure (c) per luce e gas affidarsi all'open data ARERA, che risolve
il problema alla radice.

## Storico della materia prima

- **PUN**: lo scraper calcola ogni giorno la media dei prezzi orari pubblicati
  dal GME e la accoda allo storico.
- **PSV e storico passato**: puoi importare serie storiche creando
  `data/manual_commodity.csv` con intestazione `date,pun,psv`
  (PUN in €/kWh, PSV in €/Smc). Al run successivo i valori vengono fusi nello
  storico. È il modo più semplice per popolare i grafici con anni di dati fin
  dal primo giorno (fonti: GME, ARERA, MISE — tutte pubblicano serie storiche
  scaricabili).

## Note legali e di rispetto

- Lo scraper legge **solo pagine pubbliche di listino**, una richiesta per
  sito all'ora, rispettando `robots.txt` e con User-Agent identificabile.
- Verifica comunque i **termini d'uso** dei siti monitorati: se un operatore
  non gradisce la rilevazione automatica, rimuovilo dal YAML. Per luce e gas
  la via maestra resta l'open data istituzionale ARERA.
- I prezzi mostrati sono rilevazioni automatiche **a scopo informativo**:
  il disclaimer nel footer del sito invita sempre a verificare sul sito
  ufficiale prima di sottoscrivere.

## Limiti noti / roadmap

- I selettori CSS in `providers.yaml` sono punti di partenza generici: vanno
  raffinati sito per sito dopo i primi run (guarda i log della Action).
- Le offerte mobile "operator attack" (riservate a chi proviene da altri
  operatori) spesso non compaiono sulle home pubbliche.
- Possibili evoluzioni: filtro per CAP usando l'open data ARERA, feed RSS
  delle variazioni di prezzo, badge "prezzo in calo/in salita" sulle card.
