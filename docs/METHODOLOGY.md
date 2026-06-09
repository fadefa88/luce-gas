# Methodology

Tariff Radar separates source data from interpretation.

## Source data

The dataset keeps only essential fields:

- provider
- offer name
- sector
- monthly price or energy unit price
- activation / setup cost
- expiry date when available
- promo duration when available
- constraints
- official URL
- last checked date
- confidence level

## Estimated annual cost

For mobile and fiber:

```text
annual = activation + monthly * 12
```

If an offer has a promotional period shorter than 12 months:

```text
annual = activation + promo_months * promo_price + remaining_months * full_price
```

For electricity:

```text
annual = activation + fixed_monthly * 12 + kWh_profile * (unit_price + spread)
```

For gas:

```text
annual = activation + fixed_monthly * 12 + Smc_profile * (unit_price + spread)
```

This is not a bill simulation. Taxes, network charges, dispatching, penalties and customer-specific bonuses can alter the real final cost.

## Score

The score is a heuristic signal, not a promise:

- lower monthly price improves score;
- lower activation improves score;
- larger mobile bundle improves score;
- fixed energy price may improve score when unit price is low;
- missing expiry lowers confidence;
- source type and parser quality influence confidence.

## Open Data priority

For electricity and gas, the preferred source is the Portale Offerte open data published by ARERA / Acquirente Unico. For telco, the importer reads only public offer or transparency pages.
