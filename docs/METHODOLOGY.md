# Metodologia

## Principio

Non uso profili tipo "single" o "famiglia" per ordinare le offerte energia. Il confronto principale è fatto sulle componenti:

- luce: prezzo materia prima in €/kWh;
- gas: prezzo materia prima in €/Smc;
- offerte indicizzate: indice + spread, quando estraibili;
- quota fissa mensile/annua;
- costi una tantum;
- segnali di costo nascosto: attivazione, disattivazione, recesso, modem, rate, vincoli, sconti temporanei.

Per dare un riferimento leggibile nella UI uso anche costi normalizzati non-familiari:

- luce: 1000 kWh;
- gas: 500 Smc;
- fibra: primo anno.

Sono normalizzazioni tecniche, non profili familiari.

## Luce/gas

Fonte primaria: Portale Offerte Open Data. Lo script scopre automaticamente i link correnti dalla pagina Open Data e scarica:

- offerte mercato libero elettrico XML;
- offerte mercato libero gas XML;
- dual fuel XML;
- prezzi storici degli indici pubblici CSV.

Il parser XML è volutamente difensivo perché gli schemi possono cambiare: appiattisce i nodi e cerca campi per alias.

## Fibra

Fonte: pagine pubbliche e trasparenza tariffaria degli operatori.

Lo scraper:

- rispetta robots.txt di default;
- usa delay per host;
- segue solo pochi link/PDF pertinenti;
- estrae dati minimi;
- non copia testi commerciali lunghi;
- produce audit per URL falliti o senza offerte.

## Grafici

- `commodity-index.json`: PUN/PSV storici.
- `market-correlation.json`: aggrega per mese media prezzo materia delle offerte e conteggio offerte luce/gas.
- `offer-snapshots.json`: consente di costruire storico reale degli aggiornamenti giornalieri.
