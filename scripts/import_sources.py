#!/usr/bin/env python3
"""Responsible offer importer for RadarTariffe.

The script is intentionally conservative:
- disabled sources are skipped
- robots.txt can be respected per source
- only minimal commercial fields are extracted
- no login, captcha bypass, proxy rotation or aggressive crawling
- failed extraction is stored as warning rather than guessed silently
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover
    print("Missing dependencies. Run: pip install -r requirements.txt", file=sys.stderr)
    raise exc

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OFFERS = ROOT / "data" / "offers.json"
DEFAULT_HISTORY = ROOT / "data" / "price-history.json"
DEFAULT_SOURCES = ROOT / "data" / "sources.json"


@dataclass
class ImportResult:
    offer: dict[str, Any] | None
    warning: str | None = None


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_money(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"([0-9]{1,4}(?:[.,][0-9]{1,4})?)", text.replace("\xa0", " "))
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def parse_date_it(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"([0-9]{1,2})[/-]([0-9]{1,2})[/-]([0-9]{4})", text)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def robots_allowed(url: str, user_agent: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        # If robots cannot be read, stay conservative but do not hard fail.
        return True
    return parser.can_fetch(user_agent, url)


def select_text(soup: BeautifulSoup, selector: str | None) -> str | None:
    if not selector:
        return None
    node = soup.select_one(selector)
    if not node:
        return None
    return " ".join(node.get_text(" ", strip=True).split())


def regex_text(html_text: str, pattern: str | None) -> str | None:
    if not pattern:
        return None
    match = re.search(pattern, html_text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1) if match else None


def fetch_source(source: dict[str, Any], user_agent: str, timeout: int) -> str:
    url = source["url"]
    if source.get("respectRobotsTxt", True) and not robots_allowed(url, user_agent):
        raise RuntimeError(f"robots.txt does not allow fetching {url}")
    response = requests.get(url, headers={"User-Agent": user_agent, "Accept-Language": "it-IT,it;q=0.9,en;q=0.5"}, timeout=timeout)
    response.raise_for_status()
    return response.text


def extract_offer(source: dict[str, Any], html: str) -> ImportResult:
    soup = BeautifulSoup(html, "lxml")
    rules = source.get("rules", {})
    defaults = source.get("manualDefaults", {})

    price_text = select_text(soup, rules.get("price_selector")) or regex_text(html, rules.get("price_regex"))
    activation_text = select_text(soup, rules.get("activation_selector")) or regex_text(html, rules.get("activation_regex"))
    expiry_text = select_text(soup, rules.get("expiry_selector")) or regex_text(html, rules.get("expiry_regex"))
    subtitle = select_text(soup, rules.get("subtitle_selector")) or defaults.get("subtitle") or "Offerta importata automaticamente. Revisionare prima della pubblicazione."

    price = parse_money(price_text)
    activation = parse_money(activation_text)
    expiry = parse_date_it(expiry_text) or defaults.get("expiryDate")

    if price is None:
        return ImportResult(None, f"No price found for {source.get('id')}")

    sector = source.get("sector", "unknown")
    is_energy = sector in {"luce", "gas"}
    offer = {
        "id": source["id"],
        "sector": sector,
        "provider": source.get("provider", "Provider"),
        "name": source.get("name", source["id"]),
        "subtitle": subtitle[:220],
        "status": "active",
        "type": defaults.get("type", "monthly"),
        "priceLabel": f"{str(price).replace('.', ',')} {'€/kWh' if sector == 'luce' else '€/Smc' if sector == 'gas' else '€/mese'}",
        "baseMonthly": defaults.get("baseMonthly", 0 if is_energy else price),
        "unitPrice": price if is_energy else 0,
        "spread": defaults.get("spread", 0),
        "unit": "kWh" if sector == "luce" else "Smc" if sector == "gas" else "mese",
        "activation": 0 if activation is None else activation,
        "promoMonths": defaults.get("promoMonths", 12),
        "fullPriceAfterPromo": defaults.get("fullPriceAfterPromo"),
        "expiryDate": expiry,
        "constraints": defaults.get("constraints", "Da verificare manualmente"),
        "constraintMonths": defaults.get("constraintMonths", 0),
        "sourceUrl": source["url"],
        "lastChecked": date.today().isoformat(),
        "confidence": defaults.get("confidence", 55),
        "score": defaults.get("score", 65),
        "greenScore": defaults.get("greenScore", 0),
        "hiddenCosts": defaults.get("hiddenCosts", []),
        "tags": defaults.get("tags", ["imported", "review-required"]),
    }
    return ImportResult(offer)


def merge_offers(existing: list[dict[str, Any]], imported: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {offer["id"]: offer for offer in existing}
    for offer in imported:
        current = by_id.get(offer["id"], {})
        # Preserve manually curated score if the importer did not supply a strong value.
        if current and offer.get("confidence", 0) < 80:
            offer["score"] = current.get("score", offer["score"])
        by_id[offer["id"]] = {**current, **offer}
    return sorted(by_id.values(), key=lambda item: (item.get("sector", ""), item.get("provider", ""), item.get("name", "")))


def append_history(history: list[dict[str, Any]], offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = date.today().isoformat()
    existing_keys = {(item.get("offerId"), item.get("date")) for item in history}
    for offer in offers:
        key = (offer["id"], today)
        if key in existing_keys:
            continue
        price = offer.get("unitPrice") if offer.get("sector") in {"luce", "gas"} else offer.get("baseMonthly")
        if price is None:
            continue
        history.append({"offerId": offer["id"], "date": today, "price": float(price), "monthly": float(offer.get("baseMonthly") or 0)})
    return sorted(history, key=lambda item: (item.get("offerId", ""), item.get("date", "")))


def main() -> int:
    parser = argparse.ArgumentParser(description="Import minimal offer prices from configured sources.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--offers", type=Path, default=DEFAULT_OFFERS)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_json(args.sources, {"sources": []})
    user_agent = config.get("defaultUserAgent", "RadarTariffeBot/0.1")
    sources = [source for source in config.get("sources", []) if source.get("enabled")]

    existing_offers = load_json(args.offers, [])
    history = load_json(args.history, [])
    imported: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not sources:
        print("No enabled sources. Nothing to import.")
        return 0

    for index, source in enumerate(sources, start=1):
        delay = float(source.get("politeDelaySeconds", 3))
        if index > 1 and delay > 0:
            time.sleep(delay)
        try:
            html = fetch_source(source, user_agent=user_agent, timeout=args.timeout)
            result = extract_offer(source, html)
            if result.offer:
                imported.append(result.offer)
                print(f"Imported {result.offer['id']} from {source['url']}")
            if result.warning:
                warnings.append(result.warning)
                print(f"WARNING: {result.warning}", file=sys.stderr)
        except Exception as exc:
            message = f"{source.get('id', source.get('url'))}: {exc}"
            warnings.append(message)
            print(f"WARNING: {message}", file=sys.stderr)

    merged = merge_offers(existing_offers, imported)
    updated_history = append_history(history, imported)

    if args.dry_run:
        print(json.dumps({"imported": imported, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 0

    write_json(args.offers, merged)
    write_json(args.history, updated_history)
    report = {
        "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "imported": len(imported),
        "warnings": warnings,
    }
    write_json(ROOT / "data" / "last-import-report.json", report)
    print(f"Done. Imported={len(imported)} warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
