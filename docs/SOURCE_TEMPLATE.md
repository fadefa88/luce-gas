# Source configuration template

Add sources to `data/sources.json`.

```json
{
  "id": "provider-offer",
  "enabled": true,
  "sector": "mobile",
  "provider": "Provider",
  "url": "https://provider.example/offerta",
  "strategy": "single_offer",
  "staticName": "Nome offerta",
  "patterns": {
    "price": "(?i)(9)\\s*,\\s*(99)\\s*€",
    "gb": "(?i)(250)\\s*Giga",
    "expiry": "(?i)Solo entro il\\s*(\\d{1,2})/(\\d{1,2})"
  }
}
```

Supported strategies:

- `single_offer`
- `regex_cards`
- `energy_unit`
- `energy_dual_unit`

Prefer stable official pages and transparency pages.
