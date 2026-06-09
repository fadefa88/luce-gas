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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return payload.get(key, [])


def main() -> int:
    errors: list[str] = []
    offers_path = ROOT / "data" / "offers.json"
    history_path = ROOT / "data" / "price-history.json"
    energy_path = ROOT / "data" / "energy-index.json"
    offers = load_items(offers_path, "offers")
    history = load_items(history_path, "series")
    energy = load_items(energy_path, "series")

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
            if not isinstance(value, (int, float)) or not 0 <= value <= 100:
                errors.append(f"Invalid {field} for {oid}: {value}")
        for field in ("baseMonthly", "activation"):
            value = offer.get(field, 0)
            if not isinstance(value, (int, float)) or value < 0:
                errors.append(f"Invalid {field} for {oid}: {value}")

    for series in history:
        if series.get("offerId") not in ids:
            errors.append(f"History references unknown offer: {series.get('offerId')}")
        if not isinstance(series.get("points"), list):
            errors.append(f"History series has invalid points: {series.get('offerId')}")
    for point in energy:
        if "date" not in point:
            errors.append("Energy point missing date")

    if errors:
        print("Data validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Data validation passed: {len(offers)} offers, {len(history)} history series, {len(energy)} energy points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
