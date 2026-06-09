# Tariff Radar

Osservatorio statico per offerte **luce, gas e fibra** basato su costo reale: prezzo materia prima, spread, quota fissa, costi una tantum, modem, recesso, vincoli, scadenze e fonti.

Il progetto è pensato per funzionare **senza eseguire script in locale**: import, audit, validazione e deploy sono gestiti da GitHub Actions.

## Scelta dati

### Luce e gas

La fonte primaria non è lo scraping dei siti dei singoli venditori. Il progetto usa il **Portale Offerte ARERA / Acquirente Unico - Open Data**, perché pubblica offerte mercato libero, PLACET, parametri economici e prezzi storici degli indici pubblici.

Questo è il modo più stabile per avere copertura ampia dei venditori luce/gas senza inseguire centinaia di siti commerciali.

### Fibra

Per la fibra non esiste un open dataset pubblico equivalente. Il progetto usa un registry di operatori in `data/sources.json`, con pagine ufficiali, trasparenza tariffaria e prospetti informativi quando disponibili.

Lo script fa scraping leggero: legge pagine pubbliche, segue alcuni PDF/prospetti, estrae prezzo mensile, date, velocità e segnali di costo nascosto. Non bypassa login, CAPTCHA o blocchi tecnici.

## File dati principali

- `data/offers.json`: offerte normalizzate.
- `data/sources.json`: registry fonti fibra + configurazione ARERA.
- `data/commodity-index.json`: prezzi storici PUN/PSV importati dagli Open Data.
- `data/market-correlation.json`: aggregazione mensile materie prime vs offerte.
- `data/offer-snapshots.json`: snapshot giornalieri per storico.

## Uso solo da GitHub Actions

### 1. Validare progetto

Vai su:

```text
Actions → Validate data and code → Run workflow
```

### 2. Fare audit senza modificare dati

Vai su:

```text
Actions → Audit tariff sources without commit → Run workflow
```

Scegli:

```text
all
energy-only
fiber-only
```

A fine run trovi il log negli artifact.

### 3. Aggiornare luce/gas

Vai su:

```text
Actions → Update energy data only → Run workflow
```

Questo aggiorna dati ARERA, PUN/PSV, correlazioni e snapshot.

### 4. Aggiornare fibra

Vai su:

```text
Actions → Update fiber data only → Run workflow
```

Questo interroga le fonti configurate in `data/sources.json` con delay e rispetto di `robots.txt`.

### 5. Aggiornare tutto

Vai su:

```text
Actions → Update all tariff data → Run workflow
```

### 6. Deploy GitHub Pages

Prima imposta:

```text
Settings → Pages → Build and deployment → GitHub Actions
```

Poi lancia:

```text
Actions → Deploy static site to GitHub Pages → Run workflow
```

## Schedulazioni già presenti

- `Update energy data only`: giornaliero.
- `Update fiber data only`: lunedì, mercoledì e venerdì.
- `Update all tariff data`: giornaliero completo, utile come aggiornamento generale.

Se vuoi essere ancora meno aggressivo, disattiva la schedule di `Update all tariff data` e lascia attivi solo energia + fibra separati.

## Secret consigliato

Crea questo repository secret:

```text
TARIFF_RADAR_UA=TariffRadarBot/0.3 (+https://tuodominio.it/contatti; contatto: email@dominio.it)
```

Percorso:

```text
Settings → Secrets and variables → Actions → New repository secret
```

## Modificare fonti senza locale

Apri `data/sources.json` direttamente da GitHub:

```text
data → sources.json → matita Edit → modifica URL/provider → Commit changes
```

Poi lancia:

```text
Actions → Audit tariff sources without commit
```

Se il log è sensato, lancia update fibra o update completo.

## Nota importante

Il registry fibra contiene molti operatori principali e secondari, ma va trattato come lista viva. Alcuni operatori cambiano URL, spostano PDF o usano pagine dinamiche. Lo script produce audit proprio per evidenziare fonti da correggere, invece di inventare dati.
