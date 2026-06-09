# Metodologia RadarTariffe

## Obiettivo

RadarTariffe ordina le offerte non solo per prezzo pubblicizzato, ma per costo stimato e qualità delle condizioni.

Il prezzo più visibile in pagina può non rappresentare il costo reale perché spesso non include:

- costo di attivazione;
- costo SIM o modem;
- aumento dopo la promo;
- durata minima o vincolo;
- differenza tra prezzo materia prima e costo finale;
- condizioni accessorie come domiciliazione, bolletta digitale o bundle.

## Costo annuo stimato

### Luce

```text
costo annuo = canone mensile * 12 + consumo kWh * (prezzo kWh + spread) + attivazione
```

### Gas

```text
costo annuo = canone mensile * 12 + consumo Smc * (prezzo Smc + spread) + attivazione
```

### Mobile/Fibra

```text
costo annuo = canone mensile * 12 + attivazione
```

Se la promo dura meno di 12 mesi:

```text
costo annuo = mesi promo * prezzo promo + mesi restanti * prezzo post promo + attivazione
```

## Profili di consumo demo

- Famiglia casa: 2.700 kWh e 800 Smc.
- Single smart: 1.600 kWh e 350 Smc.
- Casa energivora: 4.200 kWh e 1.300 Smc.
- Mobile data heavy: ranking per costo mensile e condizioni.
- Fibra casa: ranking per costo mensile, attivazione e vincoli.

## Score convenienza

Nel template demo lo score è presente come campo dati. In produzione puoi calcolarlo così:

```text
score = 100
  - penalità costo rispetto al miglior prezzo comparabile
  - penalità vincoli lunghi
  - penalità costi una tantum
  - penalità scadenza troppo vicina
  - penalità confidenza bassa
  + bonus prezzo stabile
  + bonus no vincolo
  + bonus fonte istituzionale/open data
```

## Confidenza dato

Valori suggeriti:

- 95-100: fonte istituzionale/open data strutturato.
- 85-94: pagina ufficiale operatore con dati chiari.
- 70-84: scraping stabile ma con selettori da monitorare.
- 50-69: regex su testo non strutturato, richiede revisione.
- <50: non pubblicare senza controllo manuale.

## Storico prezzi

Ogni import aggiunge una riga in `data/price-history.json`:

```json
{
  "offerId": "mobile-200gb-demo",
  "date": "2026-06-09",
  "price": 9.99,
  "monthly": 9.99
}
```

Lo storico serve per calcolare:

- minimo storico;
- distanza dal minimo;
- mesi in cui compaiono più promo;
- durata media delle offerte;
- frequenza delle variazioni.

## Regole editoriali

Ogni offerta deve mostrare:

- fonte;
- data ultimo controllo;
- costo stimato;
- durata promo;
- costi una tantum;
- vincoli principali;
- eventuali condizioni da verificare.

Non usare claim assoluti tipo “la migliore offerta d’Italia”. Usa formule verificabili:

```text
Offerta più conveniente nel campione, per il profilo selezionato, alla data indicata.
```
