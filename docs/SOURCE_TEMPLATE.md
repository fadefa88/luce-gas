# Template nuova fonte

Copia `data/sources.example.json` in `data/sources.json` e aggiungi una fonte.

## Fonte con regex

```json
{
  "id": "operatore-mobile-100gb",
  "enabled": true,
  "sector": "mobile",
  "provider": "Operatore",
  "name": "Mobile 100 GB",
  "url": "https://operatore.example/offerta-mobile-100gb",
  "respectRobotsTxt": true,
  "politeDelaySeconds": 3,
  "rules": {
    "price_regex": "([0-9]+,[0-9]{2})\\s*€\\s*/?mese",
    "expiry_regex": "(?:fino al|valida fino al)\\s*([0-9]{2}/[0-9]{2}/[0-9]{4})",
    "activation_regex": "attivazione[^0-9]*([0-9]+,[0-9]{2})\\s*€"
  },
  "manualDefaults": {
    "type": "monthly",
    "promoMonths": 12,
    "constraintMonths": 0,
    "confidence": 70,
    "score": 70,
    "tags": ["mobile", "imported", "review-required"]
  }
}
```

## Fonte con selettori CSS

```json
{
  "id": "provider-fibra-ftth",
  "enabled": true,
  "sector": "fibra",
  "provider": "Provider",
  "name": "Fibra FTTH",
  "url": "https://provider.example/fibra",
  "respectRobotsTxt": true,
  "politeDelaySeconds": 3,
  "rules": {
    "price_selector": ".price",
    "subtitle_selector": ".offer-summary",
    "expiry_selector": ".expiry",
    "activation_selector": ".activation-cost"
  },
  "manualDefaults": {
    "type": "monthly",
    "activation": 0,
    "promoMonths": 12,
    "constraintMonths": 24,
    "confidence": 75,
    "score": 72,
    "tags": ["fibra", "FTTH"]
  }
}
```

## Test

```bash
python scripts/import_sources.py --sources data/sources.json --dry-run
```

Se il dato è corretto:

```bash
python scripts/import_sources.py --sources data/sources.json
python scripts/validate_data.py
```
