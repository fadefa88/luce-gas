#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"id", "sector", "provider", "name", "priceLabel", "sourceUrl", "lastChecked", "score", "confidence"}
VALID_SECTORS = {"luce", "gas", "mobile", "fibra", "dual"}


def main() -> int:
    errors: list[str] = []
    offers_path = ROOT / "data" / "offers.json"
    history_path = ROOT / "data" / "price-history.json"
    offers = json.loads(offers_path.read_text(encoding="utf-8"))
    history = json.loads(history_path.read_text(encoding="utf-8"))
    ids = set()
    for index, offer in enumerate(offers):
      missing = REQUIRED - set(offer)
      if missing:
          errors.append(f"Offer #{index} missing fields: {sorted(missing)}")
      if offer.get("id") in ids:
          errors.append(f"Duplicate offer id: {offer.get('id')}")
      ids.add(offer.get("id"))
      if offer.get("sector") not in VALID_SECTORS:
          errors.append(f"Invalid sector for {offer.get('id')}: {offer.get('sector')}")
      for field in ("score", "confidence"):
          value = offer.get(field)
          if not isinstance(value, (int, float)) or not 0 <= value <= 100:
              errors.append(f"Invalid {field} for {offer.get('id')}: {value}")
    for point in history:
        if point.get("offerId") not in ids:
            errors.append(f"History references unknown offer: {point.get('offerId')}")
    if errors:
        print("Data validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Data validation passed: {len(offers)} offers, {len(history)} history points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
