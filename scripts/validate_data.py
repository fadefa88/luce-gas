#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"id", "sector", "provider", "name", "baseMonthly", "sourceUrl", "lastChecked", "score", "confidence"}
VALID_SECTORS = {"luce", "gas", "mobile", "fibra", "dual"}


def load_items(path: Path, key: str):
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return payload.get(key, [])


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main() -> int:
    errors: list[str] = []
    offers = load_items(ROOT / "data" / "offers.json", "offers")
    history = load_items(ROOT / "data" / "price-history.json", "series")
    commodity = load_items(ROOT / "data" / "commodity-index.json", "series")
    correlation = load_items(ROOT / "data" / "market-correlation.json", "series")

    ids = set()
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"Offer #{index} is not an object")
            continue
        missing = REQUIRED - set(offer)
        if missing:
            errors.append(f"Offer #{index} missing fields: {sorted(missing)}")
        oid = offer.get("id")
        if oid in ids:
            errors.append(f"Duplicate offer id: {oid}")
        ids.add(oid)
        if offer.get("sector") not in VALID_SECTORS:
            errors.append(f"Invalid sector for {oid}: {offer.get('sector')}")
        if urlparse(str(offer.get("sourceUrl", ""))).scheme not in {"http", "https"}:
            errors.append(f"Invalid sourceUrl for {oid}: {offer.get('sourceUrl')}")
        for field in ("score", "confidence"):
            value = offer.get(field)
            if not is_number(value) or not 0 <= value <= 100:
                errors.append(f"Invalid {field} for {oid}: {value}")
        for field in ("baseMonthly", "activation"):
            value = offer.get(field, 0)
            if not is_number(value) or value < 0:
                errors.append(f"Invalid {field} for {oid}: {value}")
        if offer.get("sector") == "luce" and offer.get("unitPrice") is not None and not is_number(offer.get("unitPrice")):
            errors.append(f"Invalid electricity unitPrice for {oid}: {offer.get('unitPrice')}")
        if offer.get("sector") == "gas" and offer.get("unitPrice") is not None and not is_number(offer.get("unitPrice")):
            errors.append(f"Invalid gas unitPrice for {oid}: {offer.get('unitPrice')}")
        if offer.get("hiddenCosts") is not None and not isinstance(offer.get("hiddenCosts"), list):
            errors.append(f"hiddenCosts must be list for {oid}")

    for series in history:
        if series.get("offerId") not in ids:
            errors.append(f"History references unknown offer: {series.get('offerId')}")
        if not isinstance(series.get("points"), list):
            errors.append(f"History series has invalid points: {series.get('offerId')}")
    for point in commodity:
        if "date" not in point:
            errors.append("Commodity point missing date")
    for row in correlation:
        if "month" not in row:
            errors.append("Correlation row missing month")

    if errors:
        print("Data validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Data validation passed: {len(offers)} offers, {len(history)} history series, {len(commodity)} commodity points, {len(correlation)} correlation rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
